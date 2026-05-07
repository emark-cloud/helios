// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MeanReversionV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        9_749_011_728_955_884_291_693_430_195_759_965_053_434_619_833_889_020_797_659_592_493_867_412_917_163;
    uint256 constant deltax2 =
        3_123_308_126_813_975_599_355_298_263_111_373_569_890_386_731_744_809_019_240_509_030_035_738_167_233;
    uint256 constant deltay1 =
        18_365_939_643_303_403_107_977_172_356_542_597_729_128_753_851_639_633_249_898_039_902_714_103_058_746;
    uint256 constant deltay2 =
        1_789_638_908_007_869_668_568_871_898_451_680_950_618_744_662_813_820_342_715_422_229_904_076_908_875;

    uint256 constant IC0x =
        6_237_913_527_894_357_840_044_251_931_483_612_190_318_690_744_168_221_138_243_300_819_985_780_455_610;
    uint256 constant IC0y =
        13_894_107_375_332_388_695_822_427_114_841_564_130_074_992_197_097_970_702_646_222_466_434_889_867_368;

    uint256 constant IC1x =
        18_932_397_804_043_304_162_203_831_894_272_260_160_753_106_760_652_890_735_842_592_215_025_752_618_512;
    uint256 constant IC1y =
        2_169_718_672_714_217_880_966_386_731_833_461_432_132_078_908_476_716_661_677_969_826_361_098_287_234;

    uint256 constant IC2x =
        269_306_041_824_430_977_622_757_885_175_540_380_046_067_945_282_326_000_696_970_019_971_436_508_991;
    uint256 constant IC2y =
        3_948_756_213_932_569_098_963_858_620_946_276_053_665_178_328_783_380_952_059_061_280_932_354_487_876;

    uint256 constant IC3x =
        19_648_745_599_392_492_218_122_031_545_469_803_394_896_801_884_591_246_352_193_086_278_650_538_061_837;
    uint256 constant IC3y =
        14_544_291_164_330_865_717_841_085_974_723_977_328_039_186_259_058_510_595_883_254_051_866_329_358_196;

    uint256 constant IC4x =
        12_659_554_660_088_540_222_003_593_010_975_356_335_329_261_716_280_906_859_553_710_164_412_156_458_061;
    uint256 constant IC4y =
        17_106_052_209_352_276_232_164_600_958_413_460_585_889_597_956_840_899_589_500_966_679_656_992_610_555;

    uint256 constant IC5x =
        4_867_701_952_582_889_773_195_552_155_795_164_478_915_289_406_715_023_486_506_288_516_567_549_092_047;
    uint256 constant IC5y =
        11_392_975_008_155_240_322_827_675_442_941_358_812_867_843_523_724_591_133_336_848_942_307_960_724_636;

    uint256 constant IC6x =
        16_151_556_447_351_916_896_491_344_676_271_292_907_136_514_810_056_856_650_441_114_045_973_255_627_988;
    uint256 constant IC6y =
        10_029_063_204_197_087_444_979_697_467_138_049_199_161_855_260_313_348_120_276_278_347_598_207_126_239;

    uint256 constant IC7x =
        17_790_964_115_545_003_692_076_985_743_683_639_957_453_692_594_710_676_871_635_274_142_715_365_947_973;
    uint256 constant IC7y =
        15_624_609_365_786_195_001_507_029_228_814_655_850_396_041_943_105_652_740_304_166_657_065_913_219_151;

    uint256 constant IC8x =
        8_967_089_839_000_657_646_267_285_441_438_259_787_147_371_636_358_928_540_405_072_737_688_166_801_409;
    uint256 constant IC8y =
        19_098_679_419_389_819_182_111_845_879_721_717_479_062_061_980_576_898_483_777_951_957_740_602_896_354;

    uint256 constant IC9x =
        12_504_556_298_846_478_596_236_625_632_456_144_480_422_945_940_546_027_994_265_461_291_920_723_828_605;
    uint256 constant IC9y =
        19_272_731_376_776_027_332_074_514_883_861_104_475_086_432_842_461_383_478_488_121_430_538_259_331_306;

    uint256 constant IC10x =
        11_513_546_067_658_045_509_208_316_879_411_423_047_423_271_543_318_531_753_860_661_869_990_383_778_144;
    uint256 constant IC10y =
        4_532_613_787_202_376_788_721_608_105_533_303_569_972_405_171_811_487_933_090_927_090_829_319_653_575;

    uint256 constant IC11x =
        19_194_921_197_648_484_622_660_652_615_688_824_763_699_602_269_900_238_665_685_996_798_554_906_884_530;
    uint256 constant IC11y =
        20_323_453_287_638_225_607_960_169_613_943_628_891_128_533_674_399_947_180_812_579_246_860_988_819_480;

    uint256 constant IC12x =
        14_766_511_271_893_527_398_677_757_001_070_225_586_692_796_570_012_808_161_693_438_453_707_870_229_797;
    uint256 constant IC12y =
        17_291_179_666_148_553_233_604_612_854_983_153_369_839_270_836_463_804_201_140_992_454_880_937_773_946;

    uint256 constant IC13x =
        21_415_644_174_308_284_666_593_524_755_774_391_923_658_688_666_393_323_873_973_192_540_195_948_807_927;
    uint256 constant IC13y =
        14_882_212_679_932_967_122_222_126_980_134_213_088_321_249_125_312_861_166_712_879_527_447_224_763_058;

    uint256 constant IC14x =
        16_275_230_435_981_023_290_721_273_902_902_767_184_788_433_481_027_867_184_439_485_494_138_761_258_632;
    uint256 constant IC14y =
        8_756_583_539_534_844_349_567_399_487_758_447_962_966_988_047_129_542_059_672_596_490_229_030_402_252;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
