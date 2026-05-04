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

contract YieldRotationV1Verifier {
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
        21_526_464_692_402_472_852_517_006_200_343_619_606_204_850_393_085_245_783_907_411_806_983_025_676_402;
    uint256 constant deltax2 =
        14_548_242_289_977_766_911_187_363_705_965_778_755_577_398_707_378_445_054_648_930_170_674_163_329_498;
    uint256 constant deltay1 =
        9_626_593_285_842_819_330_853_337_292_702_779_824_494_759_596_235_059_004_050_875_563_731_678_405_138;
    uint256 constant deltay2 =
        1_417_068_917_721_430_609_670_610_142_912_420_701_393_331_980_622_024_672_321_733_513_251_359_164_043;

    uint256 constant IC0x =
        2_912_215_565_323_710_946_607_746_792_066_030_939_549_261_579_150_352_881_540_398_986_308_768_989_941;
    uint256 constant IC0y =
        1_063_776_439_363_451_175_668_629_545_670_473_523_915_243_443_872_472_208_237_013_053_112_418_224_153;

    uint256 constant IC1x =
        3_795_936_176_652_590_639_493_874_450_924_232_110_306_544_759_237_921_497_885_466_404_598_578_025_023;
    uint256 constant IC1y =
        19_443_106_431_838_884_669_979_816_267_060_683_556_498_290_938_966_119_634_708_073_658_577_153_143_099;

    uint256 constant IC2x =
        3_194_780_341_117_019_784_502_235_464_465_490_090_975_272_744_833_637_562_551_003_513_894_451_438_420;
    uint256 constant IC2y =
        18_722_621_924_996_820_065_184_696_840_054_079_111_661_461_903_895_729_095_382_300_174_867_233_317_808;

    uint256 constant IC3x =
        9_258_760_881_788_776_165_620_816_761_066_275_662_337_951_533_845_729_415_912_276_557_721_830_049_052;
    uint256 constant IC3y =
        8_280_513_937_479_324_276_980_725_419_732_603_758_883_455_629_116_434_261_432_203_286_020_642_968_261;

    uint256 constant IC4x =
        10_910_281_860_704_483_204_196_438_354_474_773_323_941_905_148_545_467_590_007_126_496_370_225_039_480;
    uint256 constant IC4y =
        11_748_994_239_932_975_142_038_640_105_174_866_518_575_671_978_857_510_716_895_972_330_513_129_144_058;

    uint256 constant IC5x =
        17_595_645_893_580_528_190_033_343_636_230_685_918_279_040_707_519_386_584_462_508_179_159_046_297_861;
    uint256 constant IC5y =
        6_107_350_992_482_904_148_209_514_366_771_804_426_535_162_073_191_745_225_381_042_743_959_289_654_197;

    uint256 constant IC6x =
        12_768_832_313_173_927_752_315_453_105_918_570_007_579_894_107_050_896_998_856_765_980_994_568_517_276;
    uint256 constant IC6y =
        21_578_865_823_170_500_207_050_738_929_512_297_009_273_690_268_281_822_138_019_095_709_722_656_835_213;

    uint256 constant IC7x =
        9_285_434_027_131_109_326_372_165_975_322_418_966_556_509_158_067_775_147_905_623_537_749_389_142_793;
    uint256 constant IC7y =
        17_988_816_060_638_797_975_292_663_506_343_010_986_135_124_555_734_956_704_238_438_682_656_891_742_572;

    uint256 constant IC8x =
        6_261_291_210_370_106_716_669_437_411_651_711_711_096_811_110_515_920_511_607_007_894_721_253_824_687;
    uint256 constant IC8y =
        3_854_251_382_051_383_201_419_917_463_255_434_694_524_860_858_910_874_178_391_021_036_372_747_539_725;

    uint256 constant IC9x =
        8_552_226_900_691_238_174_182_792_317_829_143_727_899_093_719_546_639_218_578_657_773_780_345_873_319;
    uint256 constant IC9y =
        14_633_186_127_398_835_278_228_234_638_612_691_691_193_937_757_758_414_838_928_452_912_533_906_255_841;

    uint256 constant IC10x =
        11_716_889_844_072_029_214_759_276_494_914_942_954_043_137_439_981_717_662_284_718_419_856_362_447_892;
    uint256 constant IC10y =
        17_857_809_809_689_432_608_996_762_561_342_692_204_070_675_391_770_514_410_756_053_649_245_679_729_461;

    uint256 constant IC11x =
        10_513_212_604_366_147_029_172_977_015_246_981_984_572_902_467_257_168_879_937_556_983_814_475_989_335;
    uint256 constant IC11y =
        18_148_753_491_869_681_310_743_138_050_501_175_520_392_401_743_469_041_437_476_214_577_744_759_427_770;

    uint256 constant IC12x =
        15_667_292_883_405_469_357_750_626_904_139_033_946_063_523_867_055_709_407_721_160_525_008_648_357_368;
    uint256 constant IC12y =
        9_045_740_060_725_192_810_423_221_230_855_807_495_361_974_940_590_199_887_576_923_797_940_144_534_750;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[12] calldata _pubSignals
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

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
