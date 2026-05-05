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

contract MomentumV1Verifier {
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
        10_239_985_301_184_092_920_986_407_070_698_460_238_918_310_546_664_153_950_502_313_071_101_896_819_816;
    uint256 constant deltax2 =
        19_627_739_923_645_945_607_457_234_288_168_003_557_084_842_697_505_399_923_302_176_632_714_837_405_341;
    uint256 constant deltay1 =
        10_087_018_322_353_939_416_924_664_221_259_224_190_225_916_989_493_607_789_157_519_266_915_797_699_743;
    uint256 constant deltay2 =
        11_408_128_741_210_682_105_122_728_476_271_319_607_084_962_191_656_844_897_545_283_496_744_205_282_350;

    uint256 constant IC0x =
        20_798_760_812_161_754_724_143_630_437_593_866_829_596_920_520_130_890_566_008_962_095_097_415_915_730;
    uint256 constant IC0y =
        8_104_080_899_329_212_007_588_991_196_866_896_711_828_691_667_000_041_818_279_184_270_111_854_417_345;

    uint256 constant IC1x =
        16_803_035_420_305_506_227_357_642_456_511_760_881_698_086_012_033_519_024_012_430_073_016_613_039_269;
    uint256 constant IC1y =
        4_621_334_452_394_590_640_207_147_943_940_839_345_788_964_982_162_360_626_608_639_637_294_005_590_885;

    uint256 constant IC2x =
        15_658_028_402_492_649_504_826_185_857_119_843_154_954_122_940_736_271_729_119_260_808_544_551_848_621;
    uint256 constant IC2y =
        3_223_278_289_418_611_327_806_923_050_090_459_875_857_757_737_739_341_388_288_262_327_964_129_247_751;

    uint256 constant IC3x =
        13_525_941_613_276_030_563_659_084_411_240_972_290_538_904_199_408_203_487_590_394_115_333_208_819_706;
    uint256 constant IC3y =
        5_898_465_083_014_757_647_016_703_470_012_108_464_147_582_721_861_687_368_636_315_789_451_056_504_544;

    uint256 constant IC4x =
        21_353_890_303_455_027_755_028_268_981_169_682_044_730_005_046_916_798_273_262_795_186_815_377_252_344;
    uint256 constant IC4y =
        10_808_871_819_478_841_417_924_675_962_811_850_352_255_499_966_428_105_845_784_455_294_876_162_580_822;

    uint256 constant IC5x =
        14_553_221_135_447_374_939_303_760_003_297_250_377_102_311_244_072_197_405_383_083_468_535_903_600_135;
    uint256 constant IC5y =
        17_081_743_050_378_408_252_877_018_775_876_938_073_922_965_192_746_710_345_877_941_309_462_320_967_848;

    uint256 constant IC6x =
        18_045_486_187_679_110_228_813_348_083_956_485_067_563_226_024_357_789_947_784_656_855_260_538_350_056;
    uint256 constant IC6y =
        16_562_211_753_393_836_857_926_694_151_190_745_099_758_266_351_288_844_638_595_711_929_370_462_440_007;

    uint256 constant IC7x =
        9_557_123_716_599_929_091_596_526_450_751_407_493_293_304_756_253_149_563_400_016_568_931_473_885_364;
    uint256 constant IC7y =
        11_905_814_961_017_347_044_165_709_428_093_370_051_397_440_963_263_844_313_025_519_830_074_046_292_384;

    uint256 constant IC8x =
        6_944_561_395_738_536_644_200_759_431_017_809_421_824_921_718_463_607_529_149_418_545_454_682_842_853;
    uint256 constant IC8y =
        16_626_404_244_879_167_680_753_879_930_410_142_083_184_829_377_904_477_183_371_628_081_487_161_994_214;

    uint256 constant IC9x =
        19_666_717_668_672_710_281_184_787_309_548_439_501_425_856_587_672_560_673_068_348_927_358_845_006_395;
    uint256 constant IC9y =
        20_860_072_464_746_039_743_171_129_712_350_365_663_134_094_225_412_693_893_931_330_926_046_007_398_677;

    uint256 constant IC10x =
        18_335_095_938_930_349_154_406_685_821_694_074_162_462_372_904_167_750_498_573_167_569_754_858_849_644;
    uint256 constant IC10y =
        15_547_334_266_576_635_786_966_612_080_835_575_219_473_226_846_891_856_369_538_792_067_214_543_957_781;

    uint256 constant IC11x =
        17_904_168_242_119_988_887_765_250_661_767_973_466_494_616_564_515_823_996_067_650_551_793_706_029_094;
    uint256 constant IC11y =
        4_323_554_560_635_444_475_932_369_732_528_822_247_579_514_736_157_246_701_697_711_044_410_644_559_167;

    uint256 constant IC12x =
        5_699_440_426_906_401_436_845_719_641_695_251_446_331_717_724_387_053_842_372_119_957_386_443_938_340;
    uint256 constant IC12y =
        10_222_366_978_431_761_356_223_127_219_739_299_671_876_948_346_702_329_427_696_315_368_767_039_792_498;

    uint256 constant IC13x =
        20_829_484_250_285_296_020_522_245_799_209_460_133_886_603_813_021_293_993_826_905_066_443_583_873_640;
    uint256 constant IC13y =
        18_599_172_017_438_271_164_511_109_850_124_541_542_605_007_157_833_947_789_212_958_242_382_774_797_073;

    uint256 constant IC14x =
        12_506_314_911_438_012_999_694_169_421_017_174_394_896_788_814_347_100_074_170_456_696_565_582_374_035;
    uint256 constant IC14y =
        883_818_191_874_549_065_033_921_082_590_090_166_440_614_733_892_967_077_039_412_309_059_695_546_527;

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
